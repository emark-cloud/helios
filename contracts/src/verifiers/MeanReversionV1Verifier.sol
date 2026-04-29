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

contract MeanReversionV1Verifier {
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
        13_415_188_869_332_084_421_265_002_678_263_073_823_116_805_804_485_296_252_316_568_330_616_126_046_318;
    uint256 constant deltax2 =
        2_643_173_911_239_511_464_445_504_091_681_278_716_919_372_794_245_826_501_014_401_818_442_725_040_765;
    uint256 constant deltay1 =
        15_341_528_895_194_397_564_905_068_004_173_341_516_103_010_747_445_220_855_743_569_538_472_498_311_101;
    uint256 constant deltay2 =
        20_234_119_345_016_788_776_053_465_723_261_380_598_409_554_362_699_724_747_904_069_571_700_850_761_717;

    uint256 constant IC0x =
        20_624_229_349_740_356_102_994_638_616_334_930_002_555_336_249_969_283_786_214_542_211_537_553_020_723;
    uint256 constant IC0y =
        5_602_011_249_609_634_407_556_132_721_145_437_910_542_959_796_957_398_706_203_989_864_734_267_137_016;

    uint256 constant IC1x =
        9_686_234_194_332_179_651_591_431_519_982_998_360_423_066_188_602_661_058_120_232_233_417_317_511_389;
    uint256 constant IC1y =
        5_727_483_536_409_405_693_625_379_358_686_473_848_348_783_121_543_417_577_668_130_167_346_403_053_626;

    uint256 constant IC2x =
        2_917_950_222_085_474_846_346_862_647_806_589_950_349_118_595_588_099_026_261_459_993_152_360_915_253;
    uint256 constant IC2y =
        18_735_111_810_356_457_400_650_805_023_796_817_839_335_929_709_894_197_656_288_152_602_747_795_989_896;

    uint256 constant IC3x =
        20_368_451_305_550_597_049_188_940_665_843_764_550_150_822_137_802_508_712_820_662_689_187_713_154_116;
    uint256 constant IC3y =
        7_446_435_427_813_376_871_228_298_002_843_081_882_979_522_917_223_956_850_537_730_192_564_469_367_717;

    uint256 constant IC4x =
        2_415_010_618_395_402_729_605_348_564_279_008_077_067_569_275_672_607_596_393_755_640_613_305_561_126;
    uint256 constant IC4y =
        17_334_192_639_486_459_633_146_280_192_286_428_307_623_959_610_520_462_553_007_084_007_422_972_974_679;

    uint256 constant IC5x =
        17_939_851_306_713_418_666_297_154_763_345_991_997_438_207_638_674_349_779_898_197_485_919_331_173_828;
    uint256 constant IC5y =
        20_012_908_891_921_405_868_464_188_996_292_937_249_493_565_853_172_539_753_195_109_293_696_825_893_914;

    uint256 constant IC6x =
        12_034_733_949_741_220_398_547_320_439_038_052_883_328_027_039_574_415_796_101_154_707_463_848_048_548;
    uint256 constant IC6y =
        9_297_078_379_392_449_793_756_287_499_709_605_948_694_688_026_392_318_446_595_369_121_428_640_353_231;

    uint256 constant IC7x =
        19_122_606_542_865_553_408_038_190_233_702_924_488_488_174_971_923_157_216_074_378_217_126_263_006_452;
    uint256 constant IC7y =
        18_492_845_264_552_517_812_522_431_360_271_238_325_276_881_156_230_018_235_494_863_482_468_789_239_431;

    uint256 constant IC8x =
        536_888_002_862_094_721_050_855_117_180_269_347_215_210_957_015_421_929_838_794_590_679_942_126_204;
    uint256 constant IC8y =
        1_442_450_571_378_867_154_146_808_407_921_935_797_044_426_694_325_710_850_425_677_995_778_745_383_837;

    uint256 constant IC9x =
        10_751_841_018_285_161_624_010_550_825_875_997_484_605_809_637_388_752_472_618_481_362_695_865_733_020;
    uint256 constant IC9y =
        296_061_556_365_816_338_147_785_735_826_465_511_201_592_484_715_436_568_969_298_192_262_167_261_892;

    uint256 constant IC10x =
        12_794_560_006_183_680_442_107_192_349_566_544_991_184_704_058_159_791_566_645_588_398_676_808_541_393;
    uint256 constant IC10y =
        16_860_517_667_425_472_223_109_105_609_166_574_686_621_179_324_737_743_566_467_486_205_829_897_804_329;

    uint256 constant IC11x =
        16_403_037_236_960_519_160_972_704_649_746_547_664_257_535_184_336_600_075_324_260_546_901_728_018_997;
    uint256 constant IC11y =
        10_564_780_574_612_646_164_201_831_721_042_374_407_737_198_659_921_698_543_919_624_222_066_673_523_132;

    uint256 constant IC12x =
        4_375_013_506_130_935_005_516_867_606_099_912_844_496_353_294_218_309_519_032_716_675_105_219_788_629;
    uint256 constant IC12y =
        13_742_580_736_987_650_874_888_667_560_173_510_134_908_571_546_890_690_619_676_015_717_097_908_161_487;

    uint256 constant IC13x =
        19_431_507_945_805_236_113_902_550_895_075_859_632_804_937_713_988_329_263_957_723_623_247_747_875_213;
    uint256 constant IC13y =
        3_694_657_243_618_901_814_039_801_915_367_777_228_064_265_940_817_282_133_613_191_589_471_808_098_350;

    uint256 constant IC14x =
        10_209_786_185_099_666_075_007_694_625_054_302_689_678_006_246_522_462_756_381_786_530_551_575_278_501;
    uint256 constant IC14y =
        5_027_460_826_082_238_058_813_599_431_280_516_269_600_687_930_453_259_666_711_847_158_890_243_455_108;

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
