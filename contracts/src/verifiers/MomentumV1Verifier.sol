// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract MomentumV1Verifier {
    // Scalar field size
    uint256 constant r =
        21_888_242_871_839_275_222_246_405_745_257_275_088_548_364_400_416_034_343_698_204_186_575_808_495_617;
    // Base field size
    uint256 constant q =
        21_888_242_871_839_275_222_246_405_745_257_275_088_696_311_157_297_823_662_689_037_894_645_226_208_583;

    // Verification Key data
    uint256 constant alphax =
        20_491_192_805_390_485_299_153_009_773_594_534_940_189_261_866_228_447_918_068_658_471_970_481_763_042;
    uint256 constant alphay =
        9_383_485_363_053_290_200_918_347_156_157_836_566_562_967_994_039_712_273_449_902_621_266_178_545_958;
    uint256 constant betax1 =
        4_252_822_878_758_300_859_123_897_981_450_591_353_533_073_413_197_771_768_651_442_665_752_259_397_132;
    uint256 constant betax2 =
        6_375_614_351_688_725_206_403_948_262_868_962_793_625_744_043_794_305_715_222_011_528_459_656_738_731;
    uint256 constant betay1 =
        21_847_035_105_528_745_403_288_232_691_147_584_728_191_162_732_299_865_338_377_159_692_350_059_136_679;
    uint256 constant betay2 =
        10_505_242_626_370_262_277_552_901_082_094_356_697_409_835_680_220_590_971_873_171_140_371_331_206_856;
    uint256 constant gammax1 =
        11_559_732_032_986_387_107_991_004_021_392_285_783_925_812_861_821_192_530_917_403_151_452_391_805_634;
    uint256 constant gammax2 =
        10_857_046_999_023_057_135_944_570_762_232_829_481_370_756_359_578_518_086_990_519_993_285_655_852_781;
    uint256 constant gammay1 =
        4_082_367_875_863_433_681_332_203_403_145_435_568_316_851_327_593_401_208_105_741_076_214_120_093_531;
    uint256 constant gammay2 =
        8_495_653_923_123_431_417_604_973_247_489_272_438_418_190_587_263_600_148_770_280_649_306_958_101_930;
    uint256 constant deltax1 =
        6_789_609_469_643_613_826_143_064_668_109_253_853_247_637_545_482_207_022_381_181_959_483_819_007_366;
    uint256 constant deltax2 =
        2_701_650_253_299_457_942_378_102_583_794_338_415_384_614_465_322_840_188_682_898_529_793_738_872_883;
    uint256 constant deltay1 =
        483_381_707_223_362_250_533_352_380_081_213_642_457_116_358_305_367_474_515_369_675_267_285_198_305;
    uint256 constant deltay2 =
        18_309_936_292_933_193_969_170_356_102_378_091_564_342_306_887_994_284_075_493_200_230_724_499_767_732;

    uint256 constant IC0x =
        5_680_237_963_325_442_406_621_606_679_387_989_240_385_122_136_650_141_192_918_927_101_747_844_341_146;
    uint256 constant IC0y =
        17_152_572_230_056_198_861_579_350_602_906_775_569_678_015_341_259_881_941_893_098_430_270_142_748_487;

    uint256 constant IC1x =
        19_700_986_903_890_012_162_299_168_528_764_305_411_808_654_902_976_170_591_336_548_673_207_826_318_601;
    uint256 constant IC1y =
        58_969_731_808_434_899_945_064_179_578_384_295_278_118_642_580_684_303_782_593_288_211_047_917_014;

    uint256 constant IC2x =
        4_972_670_008_110_875_403_041_952_381_775_243_959_695_212_505_788_901_705_527_402_077_191_642_636_083;
    uint256 constant IC2y =
        11_356_772_410_508_085_781_255_275_545_948_240_978_167_401_889_284_775_845_355_283_113_911_398_044_149;

    uint256 constant IC3x =
        17_657_741_107_365_004_184_851_186_171_996_560_048_502_203_104_049_295_330_595_397_334_810_346_606_448;
    uint256 constant IC3y =
        13_480_769_637_118_940_644_256_872_884_929_634_634_620_835_841_198_596_205_581_376_439_326_207_033_559;

    uint256 constant IC4x =
        17_423_262_570_637_452_010_937_434_528_234_715_554_376_476_380_587_742_928_802_699_069_291_733_037_212;
    uint256 constant IC4y =
        8_955_371_191_771_050_182_053_782_971_113_575_420_965_772_092_001_651_353_342_487_964_337_910_182_731;

    uint256 constant IC5x =
        16_607_477_759_413_016_877_541_171_396_114_467_365_396_960_312_251_840_417_499_371_293_014_556_266_925;
    uint256 constant IC5y =
        7_752_731_131_027_518_023_564_421_090_160_831_532_703_843_162_593_864_142_372_334_389_461_533_876_521;

    uint256 constant IC6x =
        20_458_473_582_017_416_470_622_520_021_534_635_783_925_979_737_657_307_351_291_272_804_793_085_572_344;
    uint256 constant IC6y =
        12_116_142_084_928_091_466_010_476_952_895_170_963_473_595_286_929_798_503_139_728_386_182_071_732_503;

    uint256 constant IC7x =
        12_693_412_705_747_074_851_940_858_136_329_948_712_501_844_136_068_281_968_761_713_715_861_101_429_003;
    uint256 constant IC7y =
        15_006_241_560_301_781_249_834_424_628_347_156_189_887_956_760_616_704_841_878_712_214_820_078_609_605;

    uint256 constant IC8x =
        6_475_853_577_591_630_203_136_533_036_346_475_257_273_766_569_320_066_578_981_137_203_622_864_680_147;
    uint256 constant IC8y =
        14_810_153_901_394_734_003_118_580_312_627_255_297_486_716_619_439_874_167_730_933_590_292_638_493_483;

    uint256 constant IC9x =
        2_933_824_768_142_008_444_308_632_287_357_135_091_926_604_429_893_122_153_860_618_423_848_471_531_234;
    uint256 constant IC9y =
        3_728_507_316_704_793_904_922_124_832_052_391_347_768_418_368_731_635_046_231_926_334_961_692_309_495;

    uint256 constant IC10x =
        13_599_701_164_560_537_990_336_540_935_789_304_505_834_262_890_078_590_408_419_565_500_447_892_873_790;
    uint256 constant IC10y =
        1_238_476_230_410_082_327_234_193_325_768_443_077_282_223_067_433_227_160_240_511_060_238_014_577_471;

    uint256 constant IC11x =
        2_782_068_693_902_433_098_314_344_615_008_639_619_500_407_224_078_508_242_848_226_756_829_821_735_374;
    uint256 constant IC11y =
        20_373_789_901_047_262_331_217_089_384_895_209_420_333_702_794_217_862_644_501_546_329_722_411_381_743;

    uint256 constant IC12x =
        5_276_409_343_774_376_277_319_219_472_225_205_683_445_338_051_312_793_194_663_985_641_125_138_959_530;
    uint256 constant IC12y =
        15_753_047_752_086_952_362_880_744_864_247_215_151_943_797_220_374_063_757_459_871_094_015_385_894_815;

    uint256 constant IC13x =
        17_209_138_267_374_633_142_477_752_599_513_563_332_480_989_356_037_775_153_782_447_562_101_518_555_617;
    uint256 constant IC13y =
        3_762_375_794_025_994_124_590_805_524_865_785_660_965_415_758_609_557_360_266_333_806_855_875_624_428;

    uint256 constant IC14x =
        15_501_614_089_980_687_732_459_797_957_057_997_907_009_130_542_679_128_411_245_177_447_795_387_061;
    uint256 constant IC14y =
        406_651_841_914_011_895_281_875_450_252_679_402_401_118_889_842_817_129_648_635_617_327_348_026_016;

    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[14] calldata _pubSignals
    ) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x

                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))

                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))

                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))

                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))

                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))

                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))

                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))

                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))

                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))

                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))

                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))

                g1_mulAccC(_pVk, IC12x, IC12y, calldataload(add(pubSignals, 352)))

                g1_mulAccC(_pVk, IC13x, IC13y, calldataload(add(pubSignals, 384)))

                g1_mulAccC(_pVk, IC14x, IC14y, calldataload(add(pubSignals, 416)))

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))

                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)

                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F

            checkField(calldataload(add(_pubSignals, 0)))

            checkField(calldataload(add(_pubSignals, 32)))

            checkField(calldataload(add(_pubSignals, 64)))

            checkField(calldataload(add(_pubSignals, 96)))

            checkField(calldataload(add(_pubSignals, 128)))

            checkField(calldataload(add(_pubSignals, 160)))

            checkField(calldataload(add(_pubSignals, 192)))

            checkField(calldataload(add(_pubSignals, 224)))

            checkField(calldataload(add(_pubSignals, 256)))

            checkField(calldataload(add(_pubSignals, 288)))

            checkField(calldataload(add(_pubSignals, 320)))

            checkField(calldataload(add(_pubSignals, 352)))

            checkField(calldataload(add(_pubSignals, 384)))

            checkField(calldataload(add(_pubSignals, 416)))

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
            return(0, 0x20)
        }
    }
}
